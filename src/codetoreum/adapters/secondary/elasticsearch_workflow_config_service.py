"""ElasticsearchWorkflowConfigService — persistence-grade IWorkflowConfigService.

Replaces ``InMemoryWorkflowConfigService`` for production.  The
in-memory implementation lost every BoardWorkflowTemplate on server
restart, which breaks the BoardColumnEventHandler auto-progression
path: ``get_board_workflow_template`` returns ``None`` and the next
stage cannot be resolved.

This adapter stores BoardWorkflowTemplate instances in Elasticsearch
via ``ElasticsearchConfigStorage.save_board_workflow_template`` and
hydrates them through ``get_board_workflow_template`` on demand.  A
small per-board read-through cache (default 300s TTL) avoids hitting
ES on every column-change event.

Design notes
------------
- INV-11: no retry/circuit-breaker logic embedded.
- INV-09: explicit inheritance from ``IWorkflowConfigService``.
- INV-12: domain layer is not imported into ES.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from codetoreum.domain.board_workflow_template import (
    BoardWorkflowTemplate,
    ColumnTemplate,
    ColumnType,
)
from codetoreum.domain.pr_review_cycle_types import PRReviewCycleConfig
from codetoreum.domain.repair_cycle_types import RepairCycleAgentConfig, RepairTestType
from codetoreum.ports.exceptions import ValidationError
from codetoreum.ports.output.workflow_config_service import IWorkflowConfigService

if TYPE_CHECKING:
    from codetoreum.adapters.secondary.elasticsearch_config_storage import ElasticsearchConfigStorage

logger = logging.getLogger(__name__)

_DEFAULT_CACHE_TTL_SECONDS = 300  # 5 minutes


class ElasticsearchWorkflowConfigService(IWorkflowConfigService):
    """Read-through cache on ElasticsearchConfigStorage for BoardWorkflowTemplate."""

    def __init__(
        self,
        config_storage: ElasticsearchConfigStorage,
        cache_ttl_seconds: int = _DEFAULT_CACHE_TTL_SECONDS,
    ) -> None:
        """Initialize the adapter.

        Args:
            config_storage: Backing ``ElasticsearchConfigStorage`` instance.
            cache_ttl_seconds: How long cached templates are considered fresh.
        """
        self._config = config_storage
        self._cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[str, BoardWorkflowTemplate] = {}
        self._inserted_at: dict[str, float] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # IWorkflowConfigService
    # ------------------------------------------------------------------

    async def get_board_workflow_template(self, board_id: str) -> BoardWorkflowTemplate | None:
        cached = self._cached(board_id)
        if cached is not None:
            return cached
        try:
            doc = await self._config.get_board_workflow_template(board_id)
        except Exception as e:
            logger.error(
                f"Failed to fetch board workflow template board_id={board_id}: {e}",
                exc_info=True,
            )
            raise
        if doc is None:
            return None
        template = _template_from_doc(doc)
        self._cache_put(template)
        return template

    async def save_board_workflow_template(self, template: BoardWorkflowTemplate) -> None:
        if not template.board_id or not template.board_id.strip():
            msg = "template.board_id cannot be empty"
            raise ValidationError(msg)
        if not template.project_id or not template.project_id.strip():
            msg = "template.project_id cannot be empty"
            raise ValidationError(msg)

        doc = _template_to_doc(template)
        try:
            await self._config.save_board_workflow_template(doc)
        except Exception as e:
            logger.error(
                f"Failed to persist board workflow template board_id={template.board_id}: {e}",
                exc_info=True,
            )
            raise
        self._cache_put(template)

    async def list_board_workflow_templates(self, project_id: str) -> list[BoardWorkflowTemplate]:
        if not project_id or not project_id.strip():
            msg = "project_id cannot be empty"
            raise ValidationError(msg)
        try:
            docs = await self._config.list_board_workflow_templates(project_id)
        except Exception as e:
            logger.error(
                f"Failed to list board workflow templates project_id={project_id}: {e}",
                exc_info=True,
            )
            raise
        templates = [_template_from_doc(d) for d in docs]
        for t in templates:
            self._cache_put(t)
        return sorted(templates, key=lambda t: t.board_id)

    async def delete_board_workflow_template(self, board_id: str) -> None:
        try:
            await self._config.delete_board_workflow_template(board_id)
        except Exception as e:
            logger.error(
                f"Failed to delete board workflow template board_id={board_id}: {e}",
                exc_info=True,
            )
            raise
        with self._lock:
            self._cache.pop(board_id, None)
            self._inserted_at.pop(board_id, None)

    # ------------------------------------------------------------------
    # Cache plumbing
    # ------------------------------------------------------------------

    def _cache_put(self, template: BoardWorkflowTemplate) -> None:
        with self._lock:
            self._cache[template.board_id] = template
            self._inserted_at[template.board_id] = time.monotonic()

    def _cached(self, board_id: str) -> BoardWorkflowTemplate | None:
        with self._lock:
            self._evict_stale()
            return self._cache.get(board_id)

    def _evict_stale(self) -> None:
        if self._cache_ttl_seconds <= 0:
            return
        now = time.monotonic()
        stale = [bid for bid, ts in self._inserted_at.items() if now - ts > self._cache_ttl_seconds]
        for bid in stale:
            self._cache.pop(bid, None)
            self._inserted_at.pop(bid, None)


# ----------------------------------------------------------------------
# BoardWorkflowTemplate <-> ES document translation
# ----------------------------------------------------------------------


def _template_to_doc(template: BoardWorkflowTemplate) -> dict[str, Any]:
    """Serialize a BoardWorkflowTemplate to a dict suitable for ES storage."""
    payload = {
        "id": template.id,
        "name": template.name,
        "board_id": template.board_id,
        "project_id": template.project_id,
        "columns": [_column_to_dict(c) for c in template.columns],
        "created_at": template.created_at.isoformat() if template.created_at else None,
        "updated_at": template.updated_at.isoformat() if template.updated_at else None,
    }
    return {
        "id": template.id,
        "board_id": template.board_id,
        "project_id": template.project_id,
        "name": template.name,
        "created_at": template.created_at.isoformat() if template.created_at else datetime.now(UTC).isoformat(),
        "updated_at": template.updated_at.isoformat() if template.updated_at else datetime.now(UTC).isoformat(),
        "payload": payload,
    }


def _template_from_doc(doc: dict[str, Any]) -> BoardWorkflowTemplate:
    """Hydrate a BoardWorkflowTemplate from an ES document.

    Accepts either the wrapper shape produced by ``_template_to_doc``
    (with a ``payload`` sub-dict) or a flat shape where every field is
    at the top level — for forward-compat with future writers.
    """
    inner = doc.get("payload") if "payload" in doc else doc
    if not isinstance(inner, dict):
        msg = "Workflow template document missing payload"
        raise ValidationError(msg)

    columns_raw = inner.get("columns") or ()
    columns = tuple(_column_from_dict(c) for c in columns_raw)

    return BoardWorkflowTemplate(
        id=inner["id"],
        name=inner["name"],
        board_id=inner["board_id"],
        project_id=inner["project_id"],
        columns=columns,
        created_at=_parse_dt(inner.get("created_at")),
        updated_at=_parse_dt(inner.get("updated_at")),
    )


def _column_to_dict(column: ColumnTemplate) -> dict[str, Any]:
    return {
        "name": column.name,
        "type": column.type.value if isinstance(column.type, ColumnType) else str(column.type),
        "agent_id": column.agent_id,
        "is_pipeline_trigger": column.is_pipeline_trigger,
        "is_exit_column": column.is_exit_column,
        "position": column.position,
        "auto_progress_on_completion": column.auto_progress_on_completion,
        "sla_seconds": column.sla_seconds,
        "on_failure_column": column.on_failure_column,
        "sla_escalation_column": column.sla_escalation_column,
        "repair_cycle_agents": _dataclass_to_dict(column.repair_cycle_agents),
        "repair_cycle_test_types": (
            [t.value if isinstance(t, RepairTestType) else str(t) for t in column.repair_cycle_test_types]
            if column.repair_cycle_test_types is not None
            else None
        ),
        "pr_review_cycle_config": _dataclass_to_dict(column.pr_review_cycle_config),
        "execution_type": column.execution_type,
    }


def _column_from_dict(data: dict[str, Any]) -> ColumnTemplate:
    column_type_raw = data.get("type", "manual")
    if isinstance(column_type_raw, ColumnType):
        column_type = column_type_raw
    else:
        try:
            column_type = ColumnType(column_type_raw)
        except ValueError:
            column_type = ColumnType.MANUAL

    test_types_raw = data.get("repair_cycle_test_types")
    repair_cycle_test_types: tuple[RepairTestType, ...] | None = None
    if test_types_raw is not None:
        parsed: list[RepairTestType] = []
        for value in test_types_raw:
            if isinstance(value, RepairTestType):
                parsed.append(value)
                continue
            try:
                parsed.append(RepairTestType(value))
            except ValueError:
                continue
        repair_cycle_test_types = tuple(parsed)

    return ColumnTemplate(
        name=data["name"],
        type=column_type,
        agent_id=data.get("agent_id"),
        is_pipeline_trigger=bool(data.get("is_pipeline_trigger", False)),
        is_exit_column=bool(data.get("is_exit_column", False)),
        position=int(data["position"]),
        auto_progress_on_completion=bool(data.get("auto_progress_on_completion", False)),
        sla_seconds=data.get("sla_seconds"),
        on_failure_column=data.get("on_failure_column"),
        sla_escalation_column=data.get("sla_escalation_column"),
        repair_cycle_agents=_dataclass_from_dict(data.get("repair_cycle_agents"), RepairCycleAgentConfig),
        repair_cycle_test_types=repair_cycle_test_types,
        pr_review_cycle_config=_dataclass_from_dict(data.get("pr_review_cycle_config"), PRReviewCycleConfig),
        execution_type=data.get("execution_type", "task_queue"),
    )


def _dataclass_to_dict(value: Any) -> dict[str, Any] | None:
    """Serialize a dataclass (or None) to a plain dict for ES storage."""
    if value is None:
        return None
    if is_dataclass(value):
        return _coerce_enums(asdict(value))
    if isinstance(value, dict):
        return _coerce_enums(value)
    msg = f"Cannot serialize value of type {type(value).__name__} to dict"
    raise ValidationError(msg)


def _dataclass_from_dict(data: Any, cls: type) -> Any:
    """Reverse of ``_dataclass_to_dict`` — best effort.

    If the persisted value already matches ``cls`` (e.g., a future ES
    writer stores it natively), return it unchanged.  Otherwise call
    ``cls(**data)``; if the constructor rejects the payload, log and
    return ``None`` so the rest of the template still hydrates.
    """
    if data is None:
        return None
    if isinstance(data, cls):
        return data
    if not isinstance(data, dict):
        return None
    try:
        return cls(**data)
    except (TypeError, ValueError) as e:
        logger.warning(
            f"Failed to reconstruct {cls.__name__} from persisted dict: {e}",
            exc_info=True,
        )
        return None


def _coerce_enums(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively convert Enum instances to their .value for JSON safety."""
    out: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, Enum):
            out[key] = value.value
        elif isinstance(value, dict):
            out[key] = _coerce_enums(value)
        elif isinstance(value, (list, tuple)):
            out[key] = [v.value if isinstance(v, Enum) else v for v in value]
        else:
            out[key] = value
    return out


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
