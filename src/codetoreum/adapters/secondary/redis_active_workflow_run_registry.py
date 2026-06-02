"""RedisActiveWorkflowRunRegistry — persistence-grade IActiveWorkflowRunRegistry.

Replaces ``InMemoryActiveWorkflowRunRegistry`` for production. The in-memory
implementation loses every active-run record on restart, which is the failure
mode the duplicate-execution guard (DEF-002) relies on staying intact across
restart.

Wire format
-----------
- Key: ``codetoreum:workflow:run:{work_item_id}`` — JSON of ActiveRunInfo
  fields.
- TTL: 2 hours by default. Active runs longer than this are presumed orphaned
  and the registry forgets them; downstream code already treats a
  ``None`` result as "no active run" and emits a fresh ``WorkflowStarted``.

INV-11: no retry/circuit-breaker logic embedded.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import redis.asyncio as aioredis

from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.ports.output.active_workflow_run_registry import (
    ActiveRunInfo,
    IActiveWorkflowRunRegistry,
)

logger = logging.getLogger(__name__)

_DEFAULT_TTL_SECONDS = 60 * 60 * 2  # 2 hours
_KEY_PREFIX = "codetoreum:workflow:run"


class RedisActiveWorkflowRunRegistry(IActiveWorkflowRunRegistry):
    """Redis-backed registry for active workflow runs keyed by work_item_id."""

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

    async def set_active_run(
        self,
        work_item_id: str,
        run_id: str,
        stage_name: str,
        project_id: str,
        board_id: str,
        started_at: str,
    ) -> None:
        payload = json.dumps(
            {
                "work_item_id": work_item_id,
                "run_id": run_id,
                "stage_name": stage_name,
                "project_id": project_id,
                "board_id": board_id,
                "started_at": started_at,
            }
        )
        await self._redis.set(self._key(work_item_id), payload, ex=self._ttl_seconds)

    async def get_active_run(self, work_item_id: str) -> ActiveRunInfo | None:
        raw = await self._redis.get(self._key(work_item_id))
        if raw is None:
            return None
        return self._decode(raw, work_item_id)

    async def clear_run(self, work_item_id: str) -> None:
        await self._redis.delete(self._key(work_item_id))

    async def get_all_runs(self) -> list[tuple[str, ActiveRunInfo]]:
        out: list[tuple[str, ActiveRunInfo]] = []
        pattern = f"{self._key_prefix}:*"
        async for key in self._redis.scan_iter(match=pattern):
            key_str = key.decode("utf-8") if isinstance(key, bytes) else key
            work_item_id = key_str[len(self._key_prefix) + 1 :]
            raw = await self._redis.get(key_str)
            if raw is None:
                continue
            info = self._decode(raw, work_item_id)
            if info is not None:
                out.append((work_item_id, info))
        return out

    @staticmethod
    def _decode(raw: bytes | str, work_item_id: str) -> ActiveRunInfo | None:
        try:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            data = json.loads(raw)
            return ActiveRunInfo(
                work_item_id=data["work_item_id"],
                run_id=data["run_id"],
                stage_name=data["stage_name"],
                project_id=data["project_id"],
                board_id=data["board_id"],
                started_at=data["started_at"],
            )
        except Exception:
            logger.error(
                f"Corrupt ActiveRunInfo JSON for work_item_id={work_item_id}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_INFRASTRUCTURE_ERROR},
            )
            return None


__all__ = ["RedisActiveWorkflowRunRegistry"]
