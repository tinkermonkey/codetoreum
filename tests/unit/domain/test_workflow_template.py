"""Unit tests for WorkflowTemplate entity."""

import pytest

from codetoreum.domain.workflow_template import (
    WorkflowTemplate,
    StageTemplate,
)
from codetoreum.domain.pipeline_stage import StageType
from codetoreum.domain.exceptions import DomainError


class TestWorkflowTemplateCreation:
    """Test WorkflowTemplate creation."""

    def test_create_minimal_template(self):
        """Test creating a template with minimal parameters."""
        template = WorkflowTemplate.create(
            name="basic-workflow",
            display_name="Basic Workflow",
        )

        assert template.id is not None
        assert template.name == "basic-workflow"
        assert template.display_name == "Basic Workflow"
        assert template.description == ""
        assert template.stage_templates == []
        assert template.version == 1
        assert template.is_default is False
        assert template.applicable_labels == []
        assert template.metadata == {}
        assert template.created_at is not None
        assert template.updated_at is not None

    def test_create_template_with_all_parameters(self):
        """Test creating a template with all parameters."""
        template = WorkflowTemplate.create(
            name="advanced-workflow",
            display_name="Advanced Workflow",
            description="A complex workflow template",
            is_default=True,
        )

        assert template.name == "advanced-workflow"
        assert template.display_name == "Advanced Workflow"
        assert template.description == "A complex workflow template"
        assert template.is_default is True


class TestStageTemplateManagement:
    """Test adding and managing stage templates."""

    def test_add_stage_minimal(self):
        """Test adding a stage with minimal parameters."""
        template = WorkflowTemplate.create("test", "Test Template")

        stage = template.add_stage("stage1", "agent-1")

        assert len(template.stage_templates) == 1
        assert stage.name == "stage1"
        assert stage.agent_id == "agent-1"
        assert stage.stage_type == "sequential"
        assert stage.dependencies == []
        assert stage.is_parallel is False
        assert stage.maker_agent_id is None
        assert stage.reviewer_agent_id is None
        assert stage.max_review_iterations == 3

    def test_add_stage_with_all_parameters(self):
        """Test adding a stage with all parameters."""
        template = WorkflowTemplate.create("test", "Test Template")

        stage = template.add_stage(
            name="review-stage",
            agent_id="agent-1",
            stage_type="review",
            dependencies=["stage1"],
            is_parallel=True,
            maker_agent_id="maker-1",
            reviewer_agent_id="reviewer-1",
        )

        assert stage.name == "review-stage"
        assert stage.agent_id == "agent-1"
        assert stage.stage_type == "review"
        assert stage.dependencies == ["stage1"]
        assert stage.is_parallel is True
        assert stage.maker_agent_id == "maker-1"
        assert stage.reviewer_agent_id == "reviewer-1"

    def test_add_multiple_stages(self):
        """Test adding multiple stages."""
        template = WorkflowTemplate.create("test", "Test Template")

        template.add_stage("stage1", "agent-1")
        template.add_stage("stage2", "agent-2", dependencies=["stage1"])
        template.add_stage("stage3", "agent-3", dependencies=["stage2"])

        assert len(template.stage_templates) == 3
        assert template.stage_templates[0].name == "stage1"
        assert template.stage_templates[1].name == "stage2"
        assert template.stage_templates[2].name == "stage3"
        assert template.stage_templates[1].dependencies == ["stage1"]
        assert template.stage_templates[2].dependencies == ["stage2"]


class TestBuildStages:
    """Test building concrete pipeline stages from templates."""

    def test_build_stages_empty(self):
        """Test building stages from empty template."""
        template = WorkflowTemplate.create("test", "Test Template")
        stages = template.build_stages()
        assert stages == []

    def test_build_single_stage(self):
        """Test building a single stage."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")

        stages = template.build_stages()

        assert len(stages) == 1
        assert stages[0].name == "stage1"
        assert stages[0].agent_config["agent_id"] == "agent-1"
        assert stages[0].stage_type == StageType.SEQUENTIAL

    def test_build_multiple_stages(self):
        """Test building multiple stages."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")
        template.add_stage("stage2", "agent-2", dependencies=["stage1"])
        template.add_stage("stage3", "agent-3", dependencies=["stage2"])

        stages = template.build_stages()

        assert len(stages) == 3
        assert stages[0].name == "stage1"
        assert stages[1].name == "stage2"
        assert stages[2].name == "stage3"
        assert stages[1].dependencies == ["stage1"]
        assert stages[2].dependencies == ["stage2"]

    def test_build_stages_with_review(self):
        """Test building stages with review configuration."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage(
            "review-stage",
            "agent-1",
            stage_type="review",
            maker_agent_id="maker-1",
            reviewer_agent_id="reviewer-1",
        )

        stages = template.build_stages()

        assert len(stages) == 1
        assert stages[0].stage_type == StageType.REVIEW
        assert stages[0].stage_type == StageType.REVIEW
        assert stages[0].maker_agent_id == "maker-1"
        assert stages[0].reviewer_agent_id == "reviewer-1"


class TestTemplateValidation:
    """Test template validation logic."""

    def test_validate_simple_template(self):
        """Test validating a simple valid template."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")
        template.add_stage("stage2", "agent-2", dependencies=["stage1"])

        assert template.validate() is True

    def test_validate_invalid_dependency(self):
        """Test validation fails with invalid dependency."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1", dependencies=["nonexistent"])

        with pytest.raises(DomainError, match="Invalid dependency"):
            template.validate()

    def test_validate_circular_dependency(self):
        """Test validation fails with circular dependencies."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1", dependencies=["stage2"])
        template.add_stage("stage2", "agent-2", dependencies=["stage1"])

        with pytest.raises(DomainError, match="circular dependencies"):
            template.validate()

    def test_validate_review_stage_missing_maker(self):
        """Test validation fails for review stage without maker."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage(
            "review-stage",
            "agent-1",
            stage_type="review",
            reviewer_agent_id="reviewer-1",
        )

        with pytest.raises(DomainError, match="missing agents"):
            template.validate()

    def test_validate_review_stage_missing_reviewer(self):
        """Test validation fails for review stage without reviewer."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage(
            "review-stage",
            "agent-1",
            stage_type="review",
            maker_agent_id="maker-1",
        )

        with pytest.raises(DomainError, match="missing agents"):
            template.validate()

    def test_validate_review_stage_same_agent(self):
        """Test validation fails when maker and reviewer are the same."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage(
            "review-stage",
            "agent-1",
            stage_type="review",
            maker_agent_id="agent-1",
            reviewer_agent_id="agent-1",
        )

        with pytest.raises(DomainError, match="same maker and reviewer"):
            template.validate()

    def test_validate_complex_dependency_graph(self):
        """Test validation of complex dependency graph."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")
        template.add_stage("stage2", "agent-2", dependencies=["stage1"])
        template.add_stage("stage3", "agent-3", dependencies=["stage1"])
        template.add_stage("stage4", "agent-4", dependencies=["stage2", "stage3"])

        assert template.validate() is True


class TestCircularDependencyDetection:
    """Test circular dependency detection."""

    def test_no_cycle_linear(self):
        """Test no cycle in linear dependency chain."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")
        template.add_stage("stage2", "agent-2", dependencies=["stage1"])
        template.add_stage("stage3", "agent-3", dependencies=["stage2"])

        assert not template._has_cycles()

    def test_no_cycle_diamond(self):
        """Test no cycle in diamond dependency pattern."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")
        template.add_stage("stage2", "agent-2", dependencies=["stage1"])
        template.add_stage("stage3", "agent-3", dependencies=["stage1"])
        template.add_stage("stage4", "agent-4", dependencies=["stage2", "stage3"])

        assert not template._has_cycles()

    def test_cycle_simple(self):
        """Test detection of simple cycle."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1", dependencies=["stage2"])
        template.add_stage("stage2", "agent-2", dependencies=["stage1"])

        assert template._has_cycles()

    def test_cycle_complex(self):
        """Test detection of complex cycle."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1")
        template.add_stage("stage2", "agent-2", dependencies=["stage1"])
        template.add_stage("stage3", "agent-3", dependencies=["stage2"])
        template.add_stage("stage4", "agent-4", dependencies=["stage3", "stage1"])
        template.add_stage("stage5", "agent-5", dependencies=["stage4"])
        # Create cycle: stage2 depends on stage5
        template.stage_templates[1].dependencies.append("stage5")

        assert template._has_cycles()

    def test_self_cycle(self):
        """Test detection of self-referential cycle."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.add_stage("stage1", "agent-1", dependencies=["stage1"])

        assert template._has_cycles()


class TestCommonTemplates:
    """Test common template patterns."""

    def test_basic_sequential_template(self):
        """Test basic sequential workflow template."""
        template = WorkflowTemplate.create("basic", "Basic Sequential Workflow")
        template.add_stage("analysis", "business_analyst")
        template.add_stage("coding", "senior_engineer", dependencies=["analysis"])
        template.add_stage("testing", "test_engineer", dependencies=["coding"])

        assert len(template.stage_templates) == 3
        assert template.validate() is True

        stages = template.build_stages()
        assert len(stages) == 3

    def test_review_cycle_template(self):
        """Test workflow with review cycle template."""
        template = WorkflowTemplate.create("with-review", "Workflow with Review")
        template.add_stage("analysis", "business_analyst")
        template.add_stage(
            "coding",
            "senior_engineer",
            stage_type="review",
            dependencies=["analysis"],
            maker_agent_id="senior_engineer",
            reviewer_agent_id="tech_lead",
        )

        assert template.validate() is True

        stages = template.build_stages()
        assert len(stages) == 2
        assert stages[1].stage_type == StageType.REVIEW

    def test_parallel_stages_template(self):
        """Test workflow with parallel stages."""
        template = WorkflowTemplate.create("parallel", "Parallel Testing")
        template.add_stage("coding", "senior_engineer")
        template.add_stage(
            "unit_tests",
            "test_engineer",
            dependencies=["coding"],
            is_parallel=True,
        )
        template.add_stage(
            "integration_tests",
            "test_engineer",
            dependencies=["coding"],
            is_parallel=True,
        )

        assert template.validate() is True

        stages = template.build_stages()
        assert len(stages) == 3
        assert stages[1].is_parallel is True
        assert stages[2].is_parallel is True


class TestTemplateMetadata:
    """Test template metadata and configuration."""

    def test_applicable_labels(self):
        """Test setting applicable labels."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.applicable_labels = ["bug", "enhancement"]

        assert template.applicable_labels == ["bug", "enhancement"]

    def test_version_tracking(self):
        """Test version tracking."""
        template = WorkflowTemplate.create("test", "Test Template")
        assert template.version == 1

    def test_metadata_storage(self):
        """Test metadata storage."""
        template = WorkflowTemplate.create("test", "Test Template")
        template.metadata["custom_key"] = "custom_value"

        assert template.metadata["custom_key"] == "custom_value"

    def test_updated_at_changes_on_add_stage(self):
        """Test that updated_at changes when adding stages."""
        template = WorkflowTemplate.create("test", "Test Template")
        original_updated_at = template.updated_at

        # Add a small delay to ensure time difference
        import time
        time.sleep(0.01)

        template.add_stage("stage1", "agent-1")
        assert template.updated_at > original_updated_at
