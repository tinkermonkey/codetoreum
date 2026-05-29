"""Unit tests for ElasticsearchWorkflowConfigService using a mocked ES backend."""

from __future__ import annotations

from typing import Any

import pytest

from codetoreum.adapters.secondary.elasticsearch_workflow_config_service import (
    ElasticsearchWorkflowConfigService,
    _template_from_doc,
    _template_to_doc,
)
from codetoreum.domain.board_workflow_template import (
    BoardWorkflowTemplate,
    ColumnTemplate,
    ColumnType,
)
from codetoreum.ports.exceptions import ValidationError


class _FakeConfigStore:
    """In-memory stand-in for ElasticsearchConfigStorage."""

    def __init__(self) -> None:
        self.docs: dict[str, dict[str, Any]] = {}

    async def save_board_workflow_template(self, doc: dict[str, Any]) -> None:
        self.docs[doc["board_id"]] = dict(doc)

    async def get_board_workflow_template(self, board_id: str) -> dict[str, Any] | None:
        doc = self.docs.get(board_id)
        return dict(doc) if doc is not None else None

    async def list_board_workflow_templates(self, project_id: str) -> list[dict[str, Any]]:
        return [dict(d) for d in self.docs.values() if d.get("project_id") == project_id]

    async def delete_board_workflow_template(self, board_id: str) -> None:
        self.docs.pop(board_id, None)


def _sample_template(board_id: str = "board-1", project_id: str = "proj-1") -> BoardWorkflowTemplate:
    return BoardWorkflowTemplate(
        id=f"template-{board_id}",
        name=f"Workflow for {board_id}",
        board_id=board_id,
        project_id=project_id,
        columns=(
            ColumnTemplate(
                name="Backlog",
                type=ColumnType.MANUAL,
                agent_id=None,
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=0,
                auto_progress_on_completion=False,
            ),
            ColumnTemplate(
                name="In Progress",
                type=ColumnType.AUTOMATED,
                agent_id="agent-1",
                is_pipeline_trigger=True,
                is_exit_column=False,
                position=1,
                auto_progress_on_completion=True,
                sla_seconds=600,
                on_failure_column="Backlog",
            ),
            ColumnTemplate(
                name="Done",
                type=ColumnType.MANUAL,
                agent_id=None,
                is_pipeline_trigger=False,
                is_exit_column=True,
                position=2,
                auto_progress_on_completion=False,
            ),
        ),
    )


@pytest.fixture
def store() -> _FakeConfigStore:
    return _FakeConfigStore()


@pytest.fixture
def service(store: _FakeConfigStore) -> ElasticsearchWorkflowConfigService:
    return ElasticsearchWorkflowConfigService(config_storage=store, cache_ttl_seconds=60)  # type: ignore[arg-type]


class TestTemplateSerialization:
    def test_round_trip_preserves_columns(self) -> None:
        template = _sample_template()
        doc = _template_to_doc(template)
        restored = _template_from_doc(doc)
        assert restored.board_id == template.board_id
        assert restored.project_id == template.project_id
        assert restored.id == template.id
        assert restored.name == template.name
        assert len(restored.columns) == 3
        assert [c.name for c in restored.columns] == ["Backlog", "In Progress", "Done"]
        in_progress = restored.get_column_config("In Progress")
        assert in_progress is not None
        assert in_progress.agent_id == "agent-1"
        assert in_progress.is_pipeline_trigger is True
        assert in_progress.sla_seconds == 600
        assert in_progress.on_failure_column == "Backlog"


class TestSave:
    @pytest.mark.asyncio
    async def test_save_persists_and_caches(
        self,
        service: ElasticsearchWorkflowConfigService,
        store: _FakeConfigStore,
    ) -> None:
        template = _sample_template()
        await service.save_board_workflow_template(template)
        assert "board-1" in store.docs
        # Cached now — clear backing store and we still get it.
        store.docs.clear()
        result = await service.get_board_workflow_template("board-1")
        assert result is not None
        assert result.board_id == "board-1"

    @pytest.mark.asyncio
    async def test_save_rejects_template_with_blank_board_id(
        self,
        service: ElasticsearchWorkflowConfigService,
    ) -> None:
        # Build a valid template then mutate board_id to bypass domain
        # invariants — this proves the adapter has its own defensive check.
        template = _sample_template()
        object.__setattr__(template, "board_id", "  ")
        with pytest.raises(ValidationError):
            await service.save_board_workflow_template(template)


class TestGet:
    @pytest.mark.asyncio
    async def test_get_missing_returns_none(
        self,
        service: ElasticsearchWorkflowConfigService,
    ) -> None:
        assert await service.get_board_workflow_template("nope") is None

    @pytest.mark.asyncio
    async def test_get_cold_cache_fetches_from_es(
        self,
        service: ElasticsearchWorkflowConfigService,
        store: _FakeConfigStore,
    ) -> None:
        # Insert directly into the store without going through service.save().
        template = _sample_template()
        await store.save_board_workflow_template(_template_to_doc(template))
        result = await service.get_board_workflow_template("board-1")
        assert result is not None
        assert result.board_id == "board-1"
        assert result.get_column_config("In Progress").is_pipeline_trigger is True


class TestList:
    @pytest.mark.asyncio
    async def test_list_returns_only_project_templates_sorted(
        self,
        service: ElasticsearchWorkflowConfigService,
    ) -> None:
        await service.save_board_workflow_template(_sample_template("board-b", "proj-1"))
        await service.save_board_workflow_template(_sample_template("board-a", "proj-1"))
        await service.save_board_workflow_template(_sample_template("board-z", "proj-2"))
        templates = await service.list_board_workflow_templates("proj-1")
        assert [t.board_id for t in templates] == ["board-a", "board-b"]

    @pytest.mark.asyncio
    async def test_list_empty_project_id_raises(
        self,
        service: ElasticsearchWorkflowConfigService,
    ) -> None:
        with pytest.raises(ValidationError):
            await service.list_board_workflow_templates(" ")


class TestDelete:
    @pytest.mark.asyncio
    async def test_delete_is_idempotent(
        self,
        service: ElasticsearchWorkflowConfigService,
    ) -> None:
        await service.delete_board_workflow_template("never-existed")  # no-op

    @pytest.mark.asyncio
    async def test_delete_removes_from_cache(
        self,
        service: ElasticsearchWorkflowConfigService,
    ) -> None:
        await service.save_board_workflow_template(_sample_template())
        await service.delete_board_workflow_template("board-1")
        assert await service.get_board_workflow_template("board-1") is None
