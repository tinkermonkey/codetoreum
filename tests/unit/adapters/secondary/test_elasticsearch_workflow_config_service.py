"""Unit tests for ElasticsearchWorkflowConfigService."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from elasticsearch.exceptions import ConflictError

from codetoreum.adapters.secondary.elasticsearch_workflow_config_service import (
    ElasticsearchWorkflowConfigService,
)
from codetoreum.domain.board_workflow_template import (
    BoardWorkflowTemplate,
    ColumnTemplate,
    ColumnType,
    StageAgentConfig,
)
from codetoreum.domain.pr_review_cycle_types import PRReviewCycleConfig
from codetoreum.domain.repair_cycle_types import RepairCycleAgentConfig, RepairTestType
from codetoreum.ports.exceptions import ConcurrencyConflictError, ValidationError


@pytest.fixture
def mock_es_client():
    """Create a mock Elasticsearch client."""
    return AsyncMock()


@pytest.fixture
def config_service(mock_es_client):
    """Create an ElasticsearchWorkflowConfigService with mock client."""
    service = ElasticsearchWorkflowConfigService(
        es_client=mock_es_client,
        create_index_templates=False,
    )
    # Pre-mark as initialized to skip initialization in tests
    service._initialized = True
    return service


@pytest.fixture
def simple_column_template():
    """Create a simple column template without advanced configuration."""
    return ColumnTemplate(
        name="Backlog",
        type=ColumnType.MANUAL,
        agent_id=None,
        is_pipeline_trigger=False,
        is_exit_column=False,
        position=0,
        auto_progress_on_completion=False,
    )


@pytest.fixture
def column_with_stage_agent_config():
    """Create a column template with stage agent config."""
    return ColumnTemplate(
        name="In Progress",
        type=ColumnType.AUTOMATED,
        agent_id="agent-1",
        is_pipeline_trigger=True,
        is_exit_column=False,
        position=0,
        auto_progress_on_completion=True,
        stage_agent_config=StageAgentConfig(
            model="claude-opus-4-6",
            timeout_seconds=3600,
            permission_mode="bypassPermissions",
            output_format="stream-json",
            enable_mcp=True,
            enable_tools=True,
            max_context_tokens=8192,
            verbose=True,
            prompt_template="You are a code reviewer",
            tool_permissions={"filesystem": {"read": True, "write": False}},
            metadata={"version": "1.0"},
        ),
    )


@pytest.fixture
def column_with_repair_cycle():
    """Create a column template with repair cycle configuration."""
    return ColumnTemplate(
        name="Testing",
        type=ColumnType.AUTOMATED,
        agent_id="agent-2",
        is_pipeline_trigger=False,
        is_exit_column=False,
        position=0,
        auto_progress_on_completion=False,
        repair_cycle_agents=RepairCycleAgentConfig(
            test_execution="test-agent",
            code_fix="fix-agent",
            systemic_analysis="analysis-agent",
            systemic_fix="systemic-fix-agent",
            env_rebuild="rebuild-agent",
            env_verification="verify-agent",
            ci_check="ci-agent",
        ),
        repair_cycle_test_types=(RepairTestType.UNIT, RepairTestType.INTEGRATION, RepairTestType.E2E),
    )


@pytest.fixture
def column_with_pr_review():
    """Create a column template with PR review cycle configuration."""
    return ColumnTemplate(
        name="Code Review",
        type=ColumnType.AUTOMATED,
        agent_id="agent-3",
        is_pipeline_trigger=False,
        is_exit_column=False,
        position=0,
        auto_progress_on_completion=False,
        pr_review_cycle_config=PRReviewCycleConfig(
            max_outer_cycles=2,
            verifier_context_sources=("parent_issue", "code_context"),
            code_review_timeout_seconds=1800,
            verification_timeout_seconds=900,
            ci_check_enabled=True,
            ci_check_timeout_seconds=600,
            consolidation_timeout_seconds=900,
            sub_issue_target_board="backlog-board",
            sub_issue_creation=True,
            sub_issue_labels=("bug", "review-required"),
            sub_issue_initial_column="Backlog",
            on_issues_found_column="In Review",
            on_approved_column="Approved",
            on_failure_column="Failed",
            code_review_agent="reviewer-agent",
            verifier_agent="verifier-agent",
            consolidation_agent="consolidation-agent",
        ),
    )


@pytest.fixture
def sample_workflow_template(simple_column_template):
    """Create a sample workflow template for testing."""
    return BoardWorkflowTemplate(
        id="workflow-1",
        name="Standard Workflow",
        board_id="board-1",
        project_id="test-project",
        columns=(simple_column_template,),
    )


@pytest.fixture
def complex_workflow_template(simple_column_template):
    """Create a complex workflow with all configuration types."""
    return BoardWorkflowTemplate(
        id="workflow-complex",
        name="Complex Workflow",
        board_id="board-complex",
        project_id="test-project",
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
                stage_agent_config=StageAgentConfig(
                    model="claude-opus-4-6",
                    timeout_seconds=3600,
                    permission_mode="bypassPermissions",
                    output_format="stream-json",
                    enable_mcp=True,
                    enable_tools=True,
                    max_context_tokens=8192,
                    verbose=True,
                    prompt_template="You are a code reviewer",
                    tool_permissions={"filesystem": {"read": True, "write": False}},
                    metadata={"version": "1.0"},
                ),
            ),
            ColumnTemplate(
                name="Testing",
                type=ColumnType.AUTOMATED,
                agent_id="agent-2",
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=2,
                auto_progress_on_completion=False,
                repair_cycle_agents=RepairCycleAgentConfig(
                    test_execution="test-agent",
                    code_fix="fix-agent",
                    systemic_analysis="analysis-agent",
                    systemic_fix="systemic-fix-agent",
                    env_rebuild="rebuild-agent",
                    env_verification="verify-agent",
                    ci_check="ci-agent",
                ),
                repair_cycle_test_types=(RepairTestType.UNIT, RepairTestType.INTEGRATION, RepairTestType.E2E),
            ),
            ColumnTemplate(
                name="Code Review",
                type=ColumnType.AUTOMATED,
                agent_id="agent-3",
                is_pipeline_trigger=False,
                is_exit_column=False,
                position=3,
                auto_progress_on_completion=False,
                pr_review_cycle_config=PRReviewCycleConfig(
                    max_outer_cycles=2,
                    verifier_context_sources=("parent_issue", "code_context"),
                    code_review_timeout_seconds=1800,
                    verification_timeout_seconds=900,
                    ci_check_enabled=True,
                    ci_check_timeout_seconds=600,
                    consolidation_timeout_seconds=900,
                    sub_issue_target_board="backlog-board",
                    sub_issue_creation=True,
                    sub_issue_labels=("bug", "review-required"),
                    sub_issue_initial_column="Backlog",
                    on_issues_found_column="In Review",
                    on_approved_column="Approved",
                    on_failure_column="Failed",
                    code_review_agent="reviewer-agent",
                    verifier_agent="verifier-agent",
                    consolidation_agent="consolidation-agent",
                ),
            ),
        ),
    )


class TestSerialization:
    """Tests for serialization of workflow templates."""

    def test_serialize_simple_column(self, config_service, simple_column_template):
        """Test serialization of a column without advanced configuration."""
        template = BoardWorkflowTemplate(
            id="test-1",
            name="Test",
            board_id="board-1",
            project_id="proj-1",
            columns=(simple_column_template,),
        )

        doc = config_service._serialize_template(template, version=1)

        assert doc["id"] == "test-1"
        assert doc["name"] == "Test"
        assert doc["board_id"] == "board-1"
        assert doc["project_id"] == "proj-1"
        assert len(doc["columns"]) == 1
        assert doc["columns"][0]["name"] == "Backlog"
        assert doc["columns"][0]["type"] == "manual"
        assert "stage_agent_config" not in doc["columns"][0]

    def test_serialize_stage_agent_config(self, config_service, column_with_stage_agent_config):
        """Test serialization of stage agent config."""
        template = BoardWorkflowTemplate(
            id="test-2",
            name="Test",
            board_id="board-2",
            project_id="proj-1",
            columns=(column_with_stage_agent_config,),
        )

        doc = config_service._serialize_template(template, version=1)

        col_doc = doc["columns"][0]
        assert "stage_agent_config" in col_doc
        assert col_doc["stage_agent_config"]["model"] == "claude-opus-4-6"
        assert col_doc["stage_agent_config"]["timeout_seconds"] == 3600
        assert col_doc["stage_agent_config"]["permission_mode"] == "bypassPermissions"
        assert col_doc["stage_agent_config"]["output_format"] == "stream-json"
        assert col_doc["stage_agent_config"]["enable_mcp"] is True
        assert col_doc["stage_agent_config"]["tool_permissions"] == {
            "filesystem": {"read": True, "write": False}
        }

    def test_serialize_repair_cycle_config(self, config_service, column_with_repair_cycle):
        """Test serialization of repair cycle configuration."""
        template = BoardWorkflowTemplate(
            id="test-3",
            name="Test",
            board_id="board-3",
            project_id="proj-1",
            columns=(column_with_repair_cycle,),
        )

        doc = config_service._serialize_template(template, version=1)

        col_doc = doc["columns"][0]
        assert "repair_cycle_agents" in col_doc
        assert col_doc["repair_cycle_agents"]["test_execution"] == "test-agent"
        assert col_doc["repair_cycle_agents"]["code_fix"] == "fix-agent"
        assert "repair_cycle_test_types" in col_doc
        # RepairTestType enum values should be strings
        assert col_doc["repair_cycle_test_types"] == ["UNIT", "INTEGRATION", "E2E"]

    def test_serialize_pr_review_config(self, config_service, column_with_pr_review):
        """Test serialization of PR review cycle configuration."""
        template = BoardWorkflowTemplate(
            id="test-4",
            name="Test",
            board_id="board-4",
            project_id="proj-1",
            columns=(column_with_pr_review,),
        )

        doc = config_service._serialize_template(template, version=1)

        col_doc = doc["columns"][0]
        assert "pr_review_cycle_config" in col_doc
        assert col_doc["pr_review_cycle_config"]["max_outer_cycles"] == 2
        assert col_doc["pr_review_cycle_config"]["ci_check_enabled"] is True
        assert col_doc["pr_review_cycle_config"]["code_review_agent"] == "reviewer-agent"
        assert col_doc["pr_review_cycle_config"]["verifier_context_sources"] == [
            "parent_issue",
            "code_context",
        ]

    def test_serialize_complex_workflow(self, config_service, complex_workflow_template):
        """Test serialization of complex workflow with all configuration types."""
        doc = config_service._serialize_template(complex_workflow_template, version=1)

        assert len(doc["columns"]) == 4
        # Verify each column has expected configuration
        assert "stage_agent_config" in doc["columns"][1]
        assert "repair_cycle_agents" in doc["columns"][2]
        assert "pr_review_cycle_config" in doc["columns"][3]


class TestDeserialization:
    """Tests for deserialization of workflow templates."""

    def test_deserialize_simple_column(self, config_service):
        """Test deserialization of a column without advanced configuration."""
        doc = {
            "id": "test-1",
            "name": "Test",
            "board_id": "board-1",
            "project_id": "proj-1",
            "columns": [
                {
                    "name": "Backlog",
                    "type": "manual",
                    "agent_id": None,
                    "is_pipeline_trigger": False,
                    "is_exit_column": False,
                    "position": 0,
                    "auto_progress_on_completion": False,
                }
            ],
        }

        template = config_service._deserialize_template(doc)

        assert template.id == "test-1"
        assert template.name == "Test"
        assert len(template.columns) == 1
        assert template.columns[0].name == "Backlog"
        assert template.columns[0].stage_agent_config is None
        assert template.columns[0].repair_cycle_agents is None
        assert template.columns[0].pr_review_cycle_config is None

    def test_deserialize_stage_agent_config(self, config_service):
        """Test deserialization of stage agent config."""
        doc = {
            "id": "test-2",
            "name": "Test",
            "board_id": "board-2",
            "project_id": "proj-1",
            "columns": [
                {
                    "name": "In Progress",
                    "type": "automated",
                    "agent_id": "agent-1",
                    "is_pipeline_trigger": True,
                    "is_exit_column": False,
                    "position": 0,
                    "auto_progress_on_completion": True,
                    "stage_agent_config": {
                        "model": "claude-opus-4-6",
                        "timeout_seconds": 3600,
                        "permission_mode": "bypassPermissions",
                        "output_format": "stream-json",
                        "enable_mcp": True,
                        "enable_tools": True,
                        "max_context_tokens": 8192,
                        "verbose": True,
                        "prompt_template": "You are a code reviewer",
                        "tool_permissions": {"filesystem": {"read": True, "write": False}},
                        "metadata": {"version": "1.0"},
                    },
                }
            ],
        }

        template = config_service._deserialize_template(doc)

        col = template.columns[0]
        assert col.stage_agent_config is not None
        assert col.stage_agent_config.model == "claude-opus-4-6"
        assert col.stage_agent_config.timeout_seconds == 3600
        assert col.stage_agent_config.permission_mode == "bypassPermissions"
        assert col.stage_agent_config.output_format == "stream-json"
        assert col.stage_agent_config.enable_mcp is True
        assert col.stage_agent_config.tool_permissions == {"filesystem": {"read": True, "write": False}}

    def test_deserialize_repair_cycle_config(self, config_service):
        """Test deserialization of repair cycle configuration."""
        doc = {
            "id": "test-3",
            "name": "Test",
            "board_id": "board-3",
            "project_id": "proj-1",
            "columns": [
                {
                    "name": "Testing",
                    "type": "automated",
                    "agent_id": "agent-2",
                    "is_pipeline_trigger": False,
                    "is_exit_column": False,
                    "position": 0,
                    "auto_progress_on_completion": False,
                    "repair_cycle_agents": {
                        "test_execution": "test-agent",
                        "code_fix": "fix-agent",
                        "systemic_analysis": "analysis-agent",
                        "systemic_fix": "systemic-fix-agent",
                        "env_rebuild": "rebuild-agent",
                        "env_verification": "verify-agent",
                        "ci_check": "ci-agent",
                    },
                    "repair_cycle_test_types": ["UNIT", "INTEGRATION", "E2E"],
                }
            ],
        }

        template = config_service._deserialize_template(doc)

        col = template.columns[0]
        assert col.repair_cycle_agents is not None
        assert col.repair_cycle_agents.test_execution == "test-agent"
        assert col.repair_cycle_agents.code_fix == "fix-agent"
        assert col.repair_cycle_test_types == (RepairTestType.UNIT, RepairTestType.INTEGRATION, RepairTestType.E2E)

    def test_deserialize_pr_review_config(self, config_service):
        """Test deserialization of PR review cycle configuration."""
        doc = {
            "id": "test-4",
            "name": "Test",
            "board_id": "board-4",
            "project_id": "proj-1",
            "columns": [
                {
                    "name": "Code Review",
                    "type": "automated",
                    "agent_id": "agent-3",
                    "is_pipeline_trigger": False,
                    "is_exit_column": False,
                    "position": 0,
                    "auto_progress_on_completion": False,
                    "pr_review_cycle_config": {
                        "max_outer_cycles": 2,
                        "verifier_context_sources": ["parent_issue", "code_context"],
                        "code_review_timeout_seconds": 1800,
                        "verification_timeout_seconds": 900,
                        "ci_check_enabled": True,
                        "ci_check_timeout_seconds": 600,
                        "consolidation_timeout_seconds": 900,
                        "sub_issue_target_board": "backlog-board",
                        "sub_issue_creation": True,
                        "sub_issue_labels": ["bug", "review-required"],
                        "sub_issue_initial_column": "Backlog",
                        "on_issues_found_column": "In Review",
                        "on_approved_column": "Approved",
                        "on_failure_column": "Failed",
                        "code_review_agent": "reviewer-agent",
                        "verifier_agent": "verifier-agent",
                        "consolidation_agent": "consolidation-agent",
                    },
                }
            ],
        }

        template = config_service._deserialize_template(doc)

        col = template.columns[0]
        assert col.pr_review_cycle_config is not None
        assert col.pr_review_cycle_config.max_outer_cycles == 2
        assert col.pr_review_cycle_config.ci_check_enabled is True
        assert col.pr_review_cycle_config.code_review_agent == "reviewer-agent"


class TestBackwardCompatibility:
    """Tests for backward compatibility with documents missing new fields."""

    def test_deserialize_document_without_stage_agent_config(self, config_service):
        """Test that documents without stage_agent_config deserialize correctly."""
        doc = {
            "id": "test-1",
            "name": "Test",
            "board_id": "board-1",
            "project_id": "proj-1",
            "columns": [
                {
                    "name": "In Progress",
                    "type": "automated",
                    "agent_id": "agent-1",
                    "is_pipeline_trigger": True,
                    "is_exit_column": False,
                    "position": 0,
                    "auto_progress_on_completion": False,
                    # stage_agent_config is missing
                }
            ],
        }

        template = config_service._deserialize_template(doc)

        col = template.columns[0]
        assert col.stage_agent_config is None

    def test_deserialize_document_without_repair_cycle_config(self, config_service):
        """Test that documents without repair cycle config deserialize correctly."""
        doc = {
            "id": "test-1",
            "name": "Test",
            "board_id": "board-1",
            "project_id": "proj-1",
            "columns": [
                {
                    "name": "Testing",
                    "type": "automated",
                    "agent_id": "agent-2",
                    "is_pipeline_trigger": False,
                    "is_exit_column": False,
                    "position": 0,
                    "auto_progress_on_completion": False,
                    # repair_cycle_agents and repair_cycle_test_types are missing
                }
            ],
        }

        template = config_service._deserialize_template(doc)

        col = template.columns[0]
        assert col.repair_cycle_agents is None
        assert col.repair_cycle_test_types is None

    def test_deserialize_document_without_pr_review_config(self, config_service):
        """Test that documents without PR review config deserialize correctly."""
        doc = {
            "id": "test-1",
            "name": "Test",
            "board_id": "board-1",
            "project_id": "proj-1",
            "columns": [
                {
                    "name": "Code Review",
                    "type": "automated",
                    "agent_id": "agent-3",
                    "is_pipeline_trigger": False,
                    "is_exit_column": False,
                    "position": 0,
                    "auto_progress_on_completion": False,
                    # pr_review_cycle_config is missing
                }
            ],
        }

        template = config_service._deserialize_template(doc)

        col = template.columns[0]
        assert col.pr_review_cycle_config is None


class TestRoundTrip:
    """Tests for round-trip serialization and deserialization."""

    def test_roundtrip_simple_column(self, config_service, simple_column_template):
        """Test round-trip serialization/deserialization of simple column."""
        template = BoardWorkflowTemplate(
            id="test-1",
            name="Test",
            board_id="board-1",
            project_id="proj-1",
            columns=(simple_column_template,),
        )

        # Serialize
        doc = config_service._serialize_template(template, version=1)

        # Deserialize
        restored = config_service._deserialize_template(doc)

        assert restored.id == template.id
        assert restored.board_id == template.board_id
        assert len(restored.columns) == 1
        assert restored.columns[0].name == template.columns[0].name
        assert restored.columns[0].type == template.columns[0].type

    def test_roundtrip_complex_workflow(self, config_service, complex_workflow_template):
        """Test round-trip serialization/deserialization of complex workflow."""
        # Serialize
        doc = config_service._serialize_template(complex_workflow_template, version=1)

        # Deserialize
        restored = config_service._deserialize_template(doc)

        assert restored.id == complex_workflow_template.id
        assert restored.board_id == complex_workflow_template.board_id
        assert len(restored.columns) == 4

        # Verify stage agent config round-trip
        assert restored.columns[1].stage_agent_config is not None
        assert restored.columns[1].stage_agent_config.model == "claude-opus-4-6"
        assert restored.columns[1].stage_agent_config.permission_mode == "bypassPermissions"
        assert restored.columns[1].stage_agent_config.tool_permissions == {
            "filesystem": {"read": True, "write": False}
        }

        # Verify repair cycle round-trip
        assert restored.columns[2].repair_cycle_agents is not None
        assert restored.columns[2].repair_cycle_agents.test_execution == "test-agent"
        assert restored.columns[2].repair_cycle_test_types == (
            RepairTestType.UNIT,
            RepairTestType.INTEGRATION,
            RepairTestType.E2E,
        )

        # Verify PR review config round-trip
        assert restored.columns[3].pr_review_cycle_config is not None
        assert restored.columns[3].pr_review_cycle_config.max_outer_cycles == 2


class TestOptimisticConcurrencyControl:
    """Tests for optimistic concurrency control with ConflictError handling."""

    @pytest.mark.asyncio
    async def test_save_raises_concurrency_conflict_error_on_conflict(self, config_service, mock_es_client, sample_workflow_template):
        """Test that ConflictError from Elasticsearch is raised as ConcurrencyConflictError."""
        # Mock existing document
        mock_es_client.get.return_value = {
            "_source": {"version": 1},
            "_seq_no": 5,
            "_primary_term": 1,
        }

        # Mock Elasticsearch raising ConflictError on save
        mock_es_client.index.side_effect = ConflictError(409, "version_conflict_engine_exception", {})

        with pytest.raises(ConcurrencyConflictError) as exc_info:
            await config_service.save_board_workflow_template(sample_workflow_template)

        assert "Concurrent modification detected" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_save_passes_seq_no_and_primary_term_when_document_exists(self, config_service, mock_es_client, sample_workflow_template):
        """Test that seq_no and primary_term are passed to client.index() for existing docs."""
        # Mock existing document
        mock_es_client.get.return_value = {
            "_source": {"version": 1},
            "_seq_no": 5,
            "_primary_term": 1,
        }
        mock_es_client.index = AsyncMock()

        await config_service.save_board_workflow_template(sample_workflow_template)

        # Verify client.index was called with if_seq_no and if_primary_term
        mock_es_client.index.assert_called_once()
        call_kwargs = mock_es_client.index.call_args[1]
        assert call_kwargs["if_seq_no"] == 5
        assert call_kwargs["if_primary_term"] == 1

    @pytest.mark.asyncio
    async def test_save_without_seq_no_for_new_document(self, config_service, mock_es_client, sample_workflow_template):
        """Test that seq_no and primary_term are not passed for new documents."""
        from elasticsearch.exceptions import NotFoundError

        # Mock document not found (new document)
        mock_es_client.get.side_effect = NotFoundError(404, "not_found", {})
        mock_es_client.index = AsyncMock()

        await config_service.save_board_workflow_template(sample_workflow_template)

        # Verify client.index was called without if_seq_no and if_primary_term
        mock_es_client.index.assert_called_once()
        call_kwargs = mock_es_client.index.call_args[1]
        assert "if_seq_no" not in call_kwargs
        assert "if_primary_term" not in call_kwargs


class TestValidation:
    """Tests for input validation."""

    @pytest.mark.asyncio
    async def test_save_handles_initialization_check(self, config_service, mock_es_client, sample_workflow_template):
        """Test that save_board_workflow_template initializes the service if needed."""
        # Create a new service that is not initialized
        service = ElasticsearchWorkflowConfigService(
            es_client=mock_es_client,
            create_index_templates=False,
        )
        assert not service._initialized

        # Mock ES operations
        from elasticsearch.exceptions import NotFoundError
        mock_es_client.get.side_effect = NotFoundError(404, "not_found", {})
        mock_es_client.index = AsyncMock()

        # Call save - should not raise even though not initialized
        await service.save_board_workflow_template(sample_workflow_template)

        # Service should now be marked as initialized
        assert service._initialized


class TestEnumHandling:
    """Tests for enum serialization and deserialization."""

    def test_serialize_enum_tuple(self, config_service):
        """Test serialization of RepairTestType tuple."""
        test_types = (RepairTestType.UNIT, RepairTestType.INTEGRATION, RepairTestType.E2E)

        serialized = [test_type.value for test_type in test_types]

        assert serialized == ["UNIT", "INTEGRATION", "E2E"]

    def test_deserialize_enum_string_list(self, config_service):
        """Test deserialization of string list to RepairTestType tuple."""
        data = ["UNIT", "INTEGRATION", "E2E"]

        deserialized = config_service._deserialize_repair_cycle_test_types(data)

        assert deserialized == (RepairTestType.UNIT, RepairTestType.INTEGRATION, RepairTestType.E2E)

    def test_deserialize_enum_invalid_value(self, config_service):
        """Test that invalid enum value raises ValueError."""
        data = ["UNIT", "INVALID_TYPE", "E2E"]

        with pytest.raises(ValueError):
            config_service._deserialize_repair_cycle_test_types(data)

    def test_deserialize_enum_none(self, config_service):
        """Test that None input returns None."""
        deserialized = config_service._deserialize_repair_cycle_test_types(None)
        assert deserialized is None
