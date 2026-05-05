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
import logging
from datetime import UTC, datetime
from typing import Any

from elasticsearch import AsyncElasticsearch, NotFoundError
from elasticsearch.exceptions import ConflictError

from codetoreum.domain.board_workflow_template import (
    BoardWorkflowTemplate,
    ColumnTemplate,
    ColumnType,
    PermissionMode,
    StageAgentConfig,
)
from codetoreum.domain.pr_review_cycle_types import PRReviewCycleConfig
from codetoreum.domain.repair_cycle_types import RepairCycleAgentConfig, RepairTestType
from codetoreum.infrastructure.error_ids import ErrorRegistry
from codetoreum.ports.exceptions import ConcurrencyConflictError, ValidationError
from codetoreum.ports.output.workflow_config_service import IWorkflowConfigService

logger = logging.getLogger(__name__)


class ElasticsearchWorkflowConfigService(IWorkflowConfigService):
    """Elasticsearch-based implementation of IWorkflowConfigService.

    Stores BoardWorkflowTemplate configurations in Elasticsearch with:
    - Separate index for workflow templates (config-board-workflows)
    - Full CRUD operations keyed by board_id
    - Project-scoped listing for admin UI
    - Timestamps (created_at, updated_at) for audit trail
    - Version tracking and optimistic concurrency control (if_seq_no/if_primary_term)
    - Complete pipeline configuration including stage-specific agent configs, repair cycles,
      and PR review cycle configurations

    Index design:
    - config-board-workflows: Workflow template storage
      - Keyed by template.board_id
      - Fields include columns array, project_id, timestamps, version
      - Column nested objects include stage_agent_config, repair_cycle_agents,
        repair_cycle_test_types, and pr_review_cycle_config
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
                        "stage_agent_config": {
                            "type": "object",
                            "properties": {
                                "model": {"type": "keyword"},
                                "timeout_seconds": {"type": "integer"},
                                "permission_mode": {"type": "keyword"},
                                "output_format": {"type": "keyword"},
                                "enable_mcp": {"type": "boolean"},
                                "enable_tools": {"type": "boolean"},
                                "max_context_tokens": {"type": "integer"},
                                "verbose": {"type": "boolean"},
                                "prompt_template": {"type": "text"},
                                "tool_permissions": {"type": "object", "enabled": False},
                                "metadata": {"type": "object", "enabled": False},
                            },
                        },
                        "repair_cycle_agents": {
                            "type": "object",
                            "properties": {
                                "test_execution": {"type": "keyword"},
                                "code_fix": {"type": "keyword"},
                                "systemic_analysis": {"type": "keyword"},
                                "systemic_fix": {"type": "keyword"},
                                "env_rebuild": {"type": "keyword"},
                                "env_verification": {"type": "keyword"},
                                "ci_check": {"type": "keyword"},
                            },
                        },
                        "repair_cycle_test_types": {"type": "keyword"},
                        "pr_review_cycle_config": {
                            "type": "object",
                            "properties": {
                                "max_outer_cycles": {"type": "integer"},
                                "verifier_context_sources": {"type": "keyword"},
                                "code_review_timeout_seconds": {"type": "integer"},
                                "verification_timeout_seconds": {"type": "integer"},
                                "ci_check_enabled": {"type": "boolean"},
                                "ci_check_timeout_seconds": {"type": "integer"},
                                "consolidation_timeout_seconds": {"type": "integer"},
                                "sub_issue_target_board": {"type": "keyword"},
                                "sub_issue_creation": {"type": "boolean"},
                                "sub_issue_labels": {"type": "keyword"},
                                "sub_issue_initial_column": {"type": "keyword"},
                                "on_issues_found_column": {"type": "keyword"},
                                "on_approved_column": {"type": "keyword"},
                                "on_failure_column": {"type": "keyword"},
                                "code_review_agent": {"type": "keyword"},
                                "verifier_agent": {"type": "keyword"},
                                "consolidation_agent": {"type": "keyword"},
                            },
                        },
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

            # Try to get existing document for version tracking and optimistic concurrency control
            seq_no = None
            primary_term = None
            try:
                existing = await self.client.get(index=self.INDEX_WORKFLOWS, id=template.board_id)
                version = existing["_source"].get("version", 1) + 1
                seq_no = existing["_seq_no"]
                primary_term = existing["_primary_term"]
            except NotFoundError:
                version = 1

            # Update template with timestamps and version
            template_with_meta = dataclasses.replace(
                template, created_at=created_at, updated_at=now
            )

            doc = self._serialize_template(template_with_meta, version)

            # Use optimistic concurrency control with if_seq_no and if_primary_term
            index_kwargs = {
                "index": self.INDEX_WORKFLOWS,
                "id": template.board_id,
                "body": doc,
            }
            if seq_no is not None and primary_term is not None:
                index_kwargs["if_seq_no"] = seq_no
                index_kwargs["if_primary_term"] = primary_term

            await self.client.index(**index_kwargs)

            logger.info(f"Saved workflow template for board {template.board_id}")

        except ValidationError:
            raise
        except ConflictError as e:
            msg = (
                f"Concurrent modification detected for board {template.board_id}: "
                f"template was modified by another process"
            )
            logger.error(msg, exc_info=True, extra={"error_id": ErrorRegistry.ERR_DATABASE_ERROR})
            raise ConcurrencyConflictError(msg) from e
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

    # ── Private serialization helpers for complex types ──────────────────────

    def _serialize_stage_agent_config(self, config: StageAgentConfig) -> dict[str, Any]:
        """Serialize StageAgentConfig to dict."""
        return {
            "model": config.model,
            "timeout_seconds": config.timeout_seconds,
            "permission_mode": config.permission_mode.value if config.permission_mode else None,
            "output_format": config.output_format,
            "enable_mcp": config.enable_mcp,
            "enable_tools": config.enable_tools,
            "max_context_tokens": config.max_context_tokens,
            "verbose": config.verbose,
            "prompt_template": config.prompt_template,
            "tool_permissions": dict(config.tool_permissions) if config.tool_permissions else {},
            "metadata": dict(config.metadata) if config.metadata else {},
        }

    def _deserialize_stage_agent_config(
        self, data: dict[str, Any] | None
    ) -> StageAgentConfig | None:
        """Deserialize dict back to StageAgentConfig."""
        if data is None:
            return None

        # Convert permission_mode string value back to enum
        permission_mode_str = data.get("permission_mode")
        permission_mode = None
        if permission_mode_str:
            try:
                permission_mode = PermissionMode(permission_mode_str)
            except ValueError:
                # If the value is not a valid enum, leave it as None (use default)
                logger.warning(f"Invalid permission_mode value: {permission_mode_str}")
                permission_mode = None

        return StageAgentConfig(
            model=data.get("model"),
            timeout_seconds=data.get("timeout_seconds"),
            permission_mode=permission_mode,
            output_format=data.get("output_format"),
            enable_mcp=data.get("enable_mcp"),
            enable_tools=data.get("enable_tools"),
            max_context_tokens=data.get("max_context_tokens"),
            verbose=data.get("verbose"),
            prompt_template=data.get("prompt_template"),
            tool_permissions=data.get("tool_permissions", {}),
            metadata=data.get("metadata", {}),
        )

    def _serialize_repair_cycle_agents(self, config: RepairCycleAgentConfig) -> dict[str, Any]:
        """Serialize RepairCycleAgentConfig to dict."""
        return {
            "test_execution": config.test_execution,
            "code_fix": config.code_fix,
            "systemic_analysis": config.systemic_analysis,
            "systemic_fix": config.systemic_fix,
            "env_rebuild": config.env_rebuild,
            "env_verification": config.env_verification,
            "ci_check": config.ci_check,
        }

    def _deserialize_repair_cycle_agents(
        self, data: dict[str, Any] | None
    ) -> RepairCycleAgentConfig | None:
        """Deserialize dict back to RepairCycleAgentConfig."""
        if data is None:
            return None
        return RepairCycleAgentConfig(
            test_execution=data.get("test_execution"),
            code_fix=data.get("code_fix"),
            systemic_analysis=data.get("systemic_analysis"),
            systemic_fix=data.get("systemic_fix"),
            env_rebuild=data.get("env_rebuild"),
            env_verification=data.get("env_verification"),
            ci_check=data.get("ci_check"),
        )

    def _deserialize_repair_cycle_test_types(
        self, data: list[str] | None
    ) -> tuple[RepairTestType, ...] | None:
        """Deserialize list of test type strings back to tuple of RepairTestType."""
        if data is None:
            return None
        return tuple(RepairTestType(test_type_str) for test_type_str in data)

    def _serialize_pr_review_cycle_config(self, config: PRReviewCycleConfig) -> dict[str, Any]:
        """Serialize PRReviewCycleConfig to dict."""
        return {
            "max_outer_cycles": config.max_outer_cycles,
            "verifier_context_sources": list(config.verifier_context_sources),
            "code_review_timeout_seconds": config.code_review_timeout_seconds,
            "verification_timeout_seconds": config.verification_timeout_seconds,
            "ci_check_enabled": config.ci_check_enabled,
            "ci_check_timeout_seconds": config.ci_check_timeout_seconds,
            "consolidation_timeout_seconds": config.consolidation_timeout_seconds,
            "sub_issue_target_board": config.sub_issue_target_board,
            "sub_issue_creation": config.sub_issue_creation,
            "sub_issue_labels": list(config.sub_issue_labels),
            "sub_issue_initial_column": config.sub_issue_initial_column,
            "on_issues_found_column": config.on_issues_found_column,
            "on_approved_column": config.on_approved_column,
            "on_failure_column": config.on_failure_column,
            "code_review_agent": config.code_review_agent,
            "verifier_agent": config.verifier_agent,
            "consolidation_agent": config.consolidation_agent,
        }

    def _deserialize_pr_review_cycle_config(
        self, data: dict[str, Any] | None
    ) -> PRReviewCycleConfig | None:
        """Deserialize dict back to PRReviewCycleConfig."""
        if data is None:
            return None
        return PRReviewCycleConfig(
            max_outer_cycles=data.get("max_outer_cycles", 3),
            verifier_context_sources=tuple(data.get("verifier_context_sources", ["parent_issue"])),
            code_review_timeout_seconds=data.get("code_review_timeout_seconds", 600),
            verification_timeout_seconds=data.get("verification_timeout_seconds", 300),
            ci_check_enabled=data.get("ci_check_enabled", True),
            ci_check_timeout_seconds=data.get("ci_check_timeout_seconds", 300),
            consolidation_timeout_seconds=data.get("consolidation_timeout_seconds", 600),
            sub_issue_target_board=data.get("sub_issue_target_board"),
            sub_issue_creation=data.get("sub_issue_creation", True),
            sub_issue_labels=tuple(data.get("sub_issue_labels", [])),
            sub_issue_initial_column=data.get("sub_issue_initial_column", "Backlog"),
            on_issues_found_column=data.get("on_issues_found_column", "In Development"),
            on_approved_column=data.get("on_approved_column", "Done"),
            on_failure_column=data.get("on_failure_column"),
            code_review_agent=data.get("code_review_agent", "default-code-reviewer"),
            verifier_agent=data.get("verifier_agent", "default-verifier"),
            consolidation_agent=data.get("consolidation_agent", "default-consolidation"),
        )

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

            # Serialize stage_agent_config if present
            if col.stage_agent_config is not None:
                col_doc["stage_agent_config"] = self._serialize_stage_agent_config(
                    col.stage_agent_config
                )

            # Serialize repair_cycle_agents if present
            if col.repair_cycle_agents is not None:
                col_doc["repair_cycle_agents"] = self._serialize_repair_cycle_agents(
                    col.repair_cycle_agents
                )

            # Serialize repair_cycle_test_types if present
            if col.repair_cycle_test_types is not None:
                col_doc["repair_cycle_test_types"] = [
                    test_type.value for test_type in col.repair_cycle_test_types
                ]

            # Serialize pr_review_cycle_config if present
            if col.pr_review_cycle_config is not None:
                col_doc["pr_review_cycle_config"] = self._serialize_pr_review_cycle_config(
                    col.pr_review_cycle_config
                )

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
                stage_agent_config=self._deserialize_stage_agent_config(
                    col_doc.get("stage_agent_config")
                ),
                repair_cycle_agents=self._deserialize_repair_cycle_agents(
                    col_doc.get("repair_cycle_agents")
                ),
                repair_cycle_test_types=self._deserialize_repair_cycle_test_types(
                    col_doc.get("repair_cycle_test_types")
                ),
                pr_review_cycle_config=self._deserialize_pr_review_cycle_config(
                    col_doc.get("pr_review_cycle_config")
                ),
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
