"""Elasticsearch-backed workflow configuration service for production persistence.

This adapter provides persistent storage of BoardWorkflowTemplate configurations
in Elasticsearch, supporting the full IWorkflowConfigService contract for read/write
operations on board workflow templates.

The adapter maintains a separate index (config-board-workflows) for workflow template
storage, allowing for independent lifecycle management and scaling.

**Resilience Patterns**:
This adapter should be wrapped with resilience decorators at instantiation:
- Circuit breaker: Prevents cascading failures
- Rate limiting: Controls request rate to Elasticsearch
- Retry policy: Handles transient failures
- Timeout: Prevents indefinite waits

Example:
    ```python
    from codetoreum.infrastructure.resilience.factory import create_resilient_adapter

    workflow_config = create_resilient_adapter(
        adapter=ElasticsearchWorkflowConfigService(es_client),
        adapter_type="workflow_config_service",
        config={
            "circuit_breaker": {"failure_threshold": 5},
            "retry": {"max_attempts": 3},
            "rate_limit": {"requests_per_second": 50},
            "timeout": {"seconds": 10}
        }
    )
    ```

The adapter itself remains pure without embedded resilience logic, following
the project's hexagonal architecture principles.
"""

import dataclasses
import json
import logging
from datetime import UTC, datetime
from typing import Any

from elasticsearch import AsyncElasticsearch, NotFoundError

from codetoreum.domain.board_workflow_template import (
    BoardWorkflowTemplate,
    ColumnTemplate,
    ColumnType,
)
from codetoreum.domain.pr_review_cycle_types import PRReviewCycleConfig
from codetoreum.domain.repair_cycle_types import RepairCycleAgentConfig, RepairTestType
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.ports.exceptions import ValidationError
from codetoreum.ports.output.workflow_config_service import IWorkflowConfigService

logger = logging.getLogger(__name__)


class ElasticsearchWorkflowConfigService(IWorkflowConfigService):
    """Elasticsearch-based implementation of IWorkflowConfigService.

    Stores BoardWorkflowTemplate configurations in Elasticsearch with:
    - Separate index for workflow templates (config-board-workflows)
    - Full CRUD operations keyed by board_id
    - Project-scoped listing for admin UI
    - Timestamps (created_at, updated_at) for audit trail
    - Version tracking for optimistic concurrency control

    Index design:
    - config-board-workflows: Workflow template storage
      - Keyed by template.board_id
      - Fields include columns array, project_id, timestamps, version
    """

    # Index name for workflow templates
    INDEX_WORKFLOWS = "config-board-workflows"

    def __init__(
        self,
        es_client: AsyncElasticsearch,
        create_index_templates: bool = True,
        shard_count: int = 1,
        replica_count: int = 1,
    ):
        """Initialize Elasticsearch workflow configuration service.

        Args:
            es_client: AsyncElasticsearch client
            create_index_templates: Whether to create index templates on init
            shard_count: Number of shards for indices (configurable)
            replica_count: Number of replicas for indices (configurable)
        """
        self.client = es_client
        self._initialized = False
        self._create_index_templates = create_index_templates
        self.shard_count = shard_count
        self.replica_count = replica_count

    async def initialize(self) -> None:
        """Initialize the storage (create index and templates).

        Raises:
            Exception: If initialization fails
        """
        if self._initialized:
            return

        if self._create_index_templates:
            await self._create_index_template()

        self._initialized = True
        logger.info("Elasticsearch workflow configuration service initialized")

    async def _create_index_template(self) -> None:
        """Create or update the workflow templates index."""
        try:
            exists = await self.client.indices.exists(index=self.INDEX_WORKFLOWS)

            mappings = self._get_workflows_mapping()

            if not exists:
                await self.client.indices.create(
                    index=self.INDEX_WORKFLOWS,
                    body={
                        "settings": {
                            "number_of_shards": self.shard_count,
                            "number_of_replicas": self.replica_count,
                            "analysis": {
                                "analyzer": {
                                    "config_analyzer": {
                                        "type": "custom",
                                        "tokenizer": "standard",
                                        "filter": ["lowercase", "asciifolding", "word_delimiter"],
                                    }
                                }
                            },
                        },
                        "mappings": mappings,
                    },
                )
                logger.info(f"Created index: {self.INDEX_WORKFLOWS}")
            else:
                await self.client.indices.put_mapping(index=self.INDEX_WORKFLOWS, body=mappings)
                logger.info(f"Updated mappings for index: {self.INDEX_WORKFLOWS}")

        except Exception as e:
            logger.error(
                f"Failed to create/update index {self.INDEX_WORKFLOWS}: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_DATABASE_ERROR},
            )
            raise

    def _get_workflows_mapping(self) -> dict[str, Any]:
        """Get Elasticsearch mapping for workflow templates index."""
        return {
            "properties": {
                "id": {"type": "keyword"},
                "name": {
                    "type": "text",
                    "analyzer": "config_analyzer",
                    "fields": {"keyword": {"type": "keyword"}},
                },
                "board_id": {"type": "keyword"},
                "project_id": {"type": "keyword"},
                "columns": {
                    "type": "nested",
                    "properties": {
                        "name": {"type": "keyword"},
                        "type": {"type": "keyword"},
                        "agent_id": {"type": "keyword"},
                        "is_pipeline_trigger": {"type": "boolean"},
                        "is_exit_column": {"type": "boolean"},
                        "position": {"type": "integer"},
                        "auto_progress_on_completion": {"type": "boolean"},
                        "sla_seconds": {"type": "integer"},
                        "on_failure_column": {"type": "keyword"},
                        "sla_escalation_column": {"type": "keyword"},
                        "execution_type": {"type": "keyword"},
                    },
                },
                "created_at": {"type": "date"},
                "updated_at": {"type": "date"},
                "version": {"type": "integer"},
            }
        }

    async def get_board_workflow_template(self, board_id: str) -> BoardWorkflowTemplate | None:
        """Get the workflow template for a specific board.

        Args:
            board_id: Board identifier (matches template.board_id)

        Returns:
            BoardWorkflowTemplate if a template has been configured for this
            board, None if the board has no template.

        Raises:
            ExternalServiceError: On backing-store communication failure.
        """
        if not self._initialized:
            await self.initialize()

        try:
            result = await self.client.get(index=self.INDEX_WORKFLOWS, id=board_id)
            return self._deserialize_template(result["_source"])

        except NotFoundError:
            return None
        except Exception as e:
            logger.error(
                f"Failed to get workflow template for board {board_id}: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_DATABASE_QUERY_ERROR},
            )
            raise

    async def save_board_workflow_template(self, template: BoardWorkflowTemplate) -> None:
        """Persist or overwrite the workflow template for a board.

        Args:
            template: Fully-populated BoardWorkflowTemplate.

        Raises:
            ValidationError: If template.board_id or template.project_id is empty.
            ExternalServiceError: On backing-store communication failure.
        """
        if not template.board_id or not template.board_id.strip():
            msg = "template.board_id cannot be empty"
            raise ValidationError(msg)
        if not template.project_id or not template.project_id.strip():
            msg = "template.project_id cannot be empty"
            raise ValidationError(msg)

        if not self._initialized:
            await self.initialize()

        try:
            now = datetime.now(UTC)
            created_at = template.created_at if template.created_at is not None else now

            # Try to get existing document for version tracking
            try:
                existing = await self.client.get(index=self.INDEX_WORKFLOWS, id=template.board_id)
                version = existing["_source"].get("version", 1) + 1
            except NotFoundError:
                version = 1

            # Update template with timestamps and version
            template_with_meta = dataclasses.replace(
                template, created_at=created_at, updated_at=now
            )

            doc = self._serialize_template(template_with_meta, version)

            await self.client.index(
                index=self.INDEX_WORKFLOWS,
                id=template.board_id,
                body=doc,
            )

            logger.info(f"Saved workflow template for board {template.board_id}")

        except ValidationError:
            raise
        except Exception as e:
            logger.error(
                f"Failed to save workflow template for board {template.board_id}: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_DATABASE_ERROR},
            )
            raise

    async def list_board_workflow_templates(self, project_id: str) -> list[BoardWorkflowTemplate]:
        """List all workflow templates that belong to a project.

        Args:
            project_id: Project identifier (matches template.project_id)

        Returns:
            List of BoardWorkflowTemplate instances for the project, ordered
            by board_id. Empty list if the project has no configured boards.

        Raises:
            ValidationError: If project_id is empty.
            ExternalServiceError: On backing-store communication failure.
        """
        if not project_id or not project_id.strip():
            msg = "project_id cannot be empty"
            raise ValidationError(msg)

        if not self._initialized:
            await self.initialize()

        try:
            result = await self.client.search(
                index=self.INDEX_WORKFLOWS,
                body={
                    "query": {"term": {"project_id": project_id}},
                    "size": 100,
                    "sort": ["board_id"],
                },
            )

            templates = []
            for hit in result["hits"]["hits"]:
                templates.append(self._deserialize_template(hit["_source"]))

            return templates

        except ValidationError:
            raise
        except Exception as e:
            logger.error(
                f"Failed to list workflow templates for project {project_id}: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_DATABASE_QUERY_ERROR},
            )
            raise

    async def delete_board_workflow_template(self, board_id: str) -> None:
        """Remove the workflow template for a board.

        No-op if no template exists for board_id (idempotent).

        Args:
            board_id: Board identifier whose template should be deleted.

        Raises:
            ExternalServiceError: On backing-store communication failure.
        """
        if not self._initialized:
            await self.initialize()

        try:
            await self.client.delete(index=self.INDEX_WORKFLOWS, id=board_id, ignore=[404])
            logger.info(f"Deleted workflow template for board {board_id}")

        except Exception as e:
            logger.error(
                f"Failed to delete workflow template for board {board_id}: {e}",
                exc_info=True,
                extra={"error_id": ErrorRegistry.ERR_DATABASE_ERROR},
            )
            raise

    async def close(self) -> None:
        """Close the Elasticsearch client connection."""
        if hasattr(self.client, "close"):
            await self.client.close()
            logger.info("Closed Elasticsearch workflow config service")

    # ── Private serialization helpers ────────────────────────────────────────

    def _serialize_template(self, template: BoardWorkflowTemplate, version: int) -> dict[str, Any]:
        """Serialize a BoardWorkflowTemplate to Elasticsearch document format."""
        columns = []
        for col in template.columns:
            col_doc: dict[str, Any] = {
                "name": col.name,
                "type": col.type.value,
                "agent_id": col.agent_id,
                "is_pipeline_trigger": col.is_pipeline_trigger,
                "is_exit_column": col.is_exit_column,
                "position": col.position,
                "auto_progress_on_completion": col.auto_progress_on_completion,
                "sla_seconds": col.sla_seconds,
                "on_failure_column": col.on_failure_column,
                "sla_escalation_column": col.sla_escalation_column,
                "execution_type": col.execution_type,
            }
            columns.append(col_doc)

        return {
            "id": template.id,
            "name": template.name,
            "board_id": template.board_id,
            "project_id": template.project_id,
            "columns": columns,
            "created_at": template.created_at.isoformat() if template.created_at else None,
            "updated_at": template.updated_at.isoformat() if template.updated_at else None,
            "version": version,
        }

    def _deserialize_template(self, doc: dict[str, Any]) -> BoardWorkflowTemplate:
        """Deserialize a Elasticsearch document back to BoardWorkflowTemplate."""
        columns = []
        for col_doc in doc.get("columns", []):
            column = ColumnTemplate(
                name=col_doc["name"],
                type=ColumnType(col_doc["type"]),
                agent_id=col_doc.get("agent_id"),
                is_pipeline_trigger=col_doc["is_pipeline_trigger"],
                is_exit_column=col_doc["is_exit_column"],
                position=col_doc["position"],
                auto_progress_on_completion=col_doc["auto_progress_on_completion"],
                sla_seconds=col_doc.get("sla_seconds"),
                on_failure_column=col_doc.get("on_failure_column"),
                sla_escalation_column=col_doc.get("sla_escalation_column"),
                execution_type=col_doc.get("execution_type", "task_queue"),
            )
            columns.append(column)

        created_at = None
        if doc.get("created_at"):
            created_at = datetime.fromisoformat(doc["created_at"])

        updated_at = None
        if doc.get("updated_at"):
            updated_at = datetime.fromisoformat(doc["updated_at"])

        return BoardWorkflowTemplate(
            id=doc["id"],
            name=doc["name"],
            board_id=doc["board_id"],
            project_id=doc["project_id"],
            columns=tuple(columns),
            created_at=created_at,
            updated_at=updated_at,
        )
