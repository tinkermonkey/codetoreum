"""RedisExecutionStateTracker — persistence-grade IWorkExecutionStateTracker.

Provides fast recovery-loop lookups without replaying the full event stream.
The canonical execution state lives in the event-sourced ExecutionService; this
store enables startup recovery decisions (reconnect vs. kill) at O(1) cost.

Wire format
-----------
- Key: ``codetoreum:execution:state:{project}:{work_item_id}`` — JSON of
  execution state fields.
- TTL: 4 hours by default. Executions longer than this are presumed orphaned
  and the tracker forgets them; downstream code already treats a ``None`` result
  as "no execution state" and makes fresh recovery decisions.

INV-11: no retry/circuit-breaker logic embedded.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import redis.asyncio as aioredis

from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.ports.output.work_execution_state_tracker import (
    IWorkExecutionStateTracker,
)

logger = logging.getLogger(__name__)

_DEFAULT_TTL_SECONDS = 60 * 60 * 4  # 4 hours
_KEY_PREFIX = "codetoreum:execution:state"


class RedisExecutionStateTracker(IWorkExecutionStateTracker):
    """Redis-backed tracker for work execution state keyed by project:work_item_id."""

    def __init__(
        self,
        redis_client: aioredis.Redis,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
        key_prefix: str = _KEY_PREFIX,
    ) -> None:
        self._redis = redis_client
        self._ttl_seconds = ttl_seconds
        self._key_prefix = key_prefix

    def _key(self, project: str, work_item_id: str) -> str:
        return f"{self._key_prefix}:{project}:{work_item_id}"

    async def load_state(self, project: str, work_item_id: str) -> dict[str, Any] | None:
        """Load execution state from storage.

        Retrieves the execution state for a specific work item. Returns None
        if no state exists or the state has expired.

        Args:
            project: Project identifier
            work_item_id: Work item identifier

        Returns:
            Dictionary containing execution state if found and not expired,
            None otherwise

        Raises:
            StorageError: If storage read fails
        """
        try:
            raw = await self._redis.get(self._key(project, work_item_id))
            if raw is None:
                return None
            return self._decode(raw, project, work_item_id)
        except Exception:
            logger.error(
                f"Failed to load execution state for project={project}, work_item_id={work_item_id}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
            )
            raise

    async def mark_execution_failed(
        self, project: str, work_item_id: str, agent: str, reason: str
    ) -> None:
        """Mark an execution as failed with a reason.

        Records that an execution has failed, typically during recovery
        operations when a container cannot be reconnected.

        Args:
            project: Project identifier
            work_item_id: Work item identifier
            agent: Agent identifier that was executing
            reason: Reason for the failure

        Returns:
            None (void operation)

        Raises:
            StorageError: If storage write fails

        Contract:
            - Failure record is persisted atomically
            - Record has TTL of 4 hours
            - Multiple marks are idempotent
            - All fields are preserved exactly
        """
        try:
            payload = json.dumps(
                {
                    "status": "failed",
                    "agent": agent,
                    "reason": reason,
                }
            )
            await self._redis.set(
                self._key(project, work_item_id), payload, ex=self._ttl_seconds
            )
        except Exception:
            logger.error(
                f"Failed to mark execution as failed for project={project}, work_item_id={work_item_id}, agent={agent}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
            )
            raise

    @staticmethod
    def _decode(raw: bytes | str, project: str, work_item_id: str) -> dict[str, Any] | None:
        try:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            data = json.loads(raw)
            return data
        except Exception:
            logger.error(
                f"Corrupt execution state JSON for project={project}, work_item_id={work_item_id}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
            )
            return None


__all__ = ["RedisExecutionStateTracker"]
