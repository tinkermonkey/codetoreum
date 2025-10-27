"""Unit tests for WorkflowValidationService."""

import pytest

from codetoreum.domain.services.workflow_validation_service import (
    WorkflowValidationService,
)
from codetoreum.domain.workflow_template import WorkflowTemplate


@pytest.fixture
def valid_template():
    """Create a valid workflow template."""
    template = WorkflowTemplate.create(
        name="standard_workflow",
        display_name="Standard Workflow",
        description="Standard development workflow",
    )
    template.add_stage("analysis", "agent_1", stage_type="sequential")
    template.add_stage("implementation", "agent_2", dependencies=["analysis"])
    template.add_stage("testing", "agent_3", dependencies=["implementation"])
    return template


class TestValidateWorkflowTemplate:
    """Tests for validate_workflow_template method."""

    def test_valid_template_returns_no_errors(self, valid_template):
        """Test that valid template returns empty error list."""
        errors = WorkflowValidationService.validate_workflow_template(valid_template)
        assert errors == []

    def test_empty_template_returns_error(self):
        """Test that template with no stages returns error."""
        template = WorkflowTemplate.create(
            name="empty", display_name="Empty", description="Empty template"
        )

        errors = WorkflowValidationService.validate_workflow_template(template)

        assert len(errors) == 1
        assert "at least one stage" in errors[0]

    def test_invalid_dependency_returns_error(self):
        """Test that invalid dependency returns error."""
        template = WorkflowTemplate.create(
            name="invalid_dep", display_name="Invalid Dependency"
        )
        template.add_stage("stage1", "agent_1", dependencies=["nonexistent"])

        errors = WorkflowValidationService.validate_workflow_template(template)

        assert any("invalid dependency" in err.lower() for err in errors)
        assert any("nonexistent" in err for err in errors)

    def test_circular_dependency_returns_error(self):
        """Test that circular dependencies are detected."""
        template = WorkflowTemplate.create(
            name="circular", display_name="Circular Dependencies"
        )
        template.add_stage("stage1", "agent_1", dependencies=["stage2"])
        template.add_stage("stage2", "agent_2", dependencies=["stage1"])

        errors = WorkflowValidationService.validate_workflow_template(template)

        assert any("circular" in err.lower() for err in errors)

    def test_review_stage_missing_maker_returns_error(self):
        """Test that review stage without maker agent returns error."""
        template = WorkflowTemplate.create(
            name="invalid_review", display_name="Invalid Review"
        )
        template.add_stage(
            "review",
            "agent_1",
            stage_type="review",
            maker_agent_id=None,  # Missing
            reviewer_agent_id="reviewer_1",
        )

        errors = WorkflowValidationService.validate_workflow_template(template)

        assert any("missing maker agent" in err.lower() for err in errors)

    def test_review_stage_missing_reviewer_returns_error(self):
        """Test that review stage without reviewer agent returns error."""
        template = WorkflowTemplate.create(
            name="invalid_review", display_name="Invalid Review"
        )
        template.add_stage(
            "review",
            "agent_1",
            stage_type="review",
            maker_agent_id="maker_1",
            reviewer_agent_id=None,  # Missing
        )

        errors = WorkflowValidationService.validate_workflow_template(template)

        assert any("missing reviewer agent" in err.lower() for err in errors)

    def test_review_stage_same_maker_and_reviewer_returns_error(self):
        """Test that review stage with same maker and reviewer returns error."""
        template = WorkflowTemplate.create(
            name="invalid_review", display_name="Invalid Review"
        )
        template.add_stage(
            "review",
            "agent_1",
            stage_type="review",
            maker_agent_id="same_agent",
            reviewer_agent_id="same_agent",  # Same as maker
        )

        errors = WorkflowValidationService.validate_workflow_template(template)

        assert any("same maker and reviewer" in err.lower() for err in errors)

    def test_too_many_parallel_stages_returns_error(self):
        """Test that too many parallel stages returns error."""
        template = WorkflowTemplate.create(
            name="too_many_parallel", display_name="Too Many Parallel"
        )
        # Add 11 parallel stages (exceeds limit of 10)
        for i in range(11):
            template.add_stage(f"parallel_{i}", f"agent_{i}", is_parallel=True)

        errors = WorkflowValidationService.validate_workflow_template(template)

        assert any("too many parallel stages" in err.lower() for err in errors)

    def test_duplicate_stage_names_returns_error(self):
        """Test that duplicate stage names return error."""
        template = WorkflowTemplate.create(
            name="duplicate_names", display_name="Duplicate Names"
        )
        template.add_stage("stage1", "agent_1")
        template.add_stage("stage1", "agent_2")  # Duplicate name

        errors = WorkflowValidationService.validate_workflow_template(template)

        assert any("must be unique" in err.lower() for err in errors)

    def test_empty_stage_name_returns_error(self):
        """Test that empty stage name returns error."""
        template = WorkflowTemplate.create(
            name="empty_name", display_name="Empty Stage Name"
        )
        template.add_stage("", "agent_1")  # Empty name

        errors = WorkflowValidationService.validate_workflow_template(template)

        assert any("cannot be empty" in err.lower() for err in errors)

    def test_empty_agent_id_returns_error(self):
        """Test that empty agent ID returns error."""
        template = WorkflowTemplate.create(
            name="empty_agent", display_name="Empty Agent ID"
        )
        template.add_stage("stage1", "")  # Empty agent ID

        errors = WorkflowValidationService.validate_workflow_template(template)

        assert any("missing agent id" in err.lower() for err in errors)

    def test_multiple_errors_returned(self):
        """Test that multiple errors are collected and returned."""
        template = WorkflowTemplate.create(
            name="multiple_errors", display_name="Multiple Errors"
        )
        template.add_stage("stage1", "agent_1", dependencies=["nonexistent"])
        template.add_stage("stage2", "agent_2", dependencies=["stage1"])
        template.add_stage(
            "review",
            "agent_3",
            stage_type="review",
            maker_agent_id=None,
            reviewer_agent_id=None,
        )

        errors = WorkflowValidationService.validate_workflow_template(template)

        # Should have multiple errors: invalid dependency, missing maker, missing reviewer
        assert len(errors) >= 3

    def test_complex_valid_workflow(self):
        """Test complex but valid workflow."""
        template = WorkflowTemplate.create(
            name="complex", display_name="Complex Workflow"
        )

        # Sequential stages
        template.add_stage("analysis", "analyst")
        template.add_stage("design", "architect", dependencies=["analysis"])

        # Parallel stages
        template.add_stage(
            "impl_frontend", "frontend_dev", dependencies=["design"], is_parallel=True
        )
        template.add_stage(
            "impl_backend", "backend_dev", dependencies=["design"], is_parallel=True
        )

        # Review stage
        template.add_stage(
            "code_review",
            "reviewer",
            stage_type="review",
            dependencies=["impl_frontend", "impl_backend"],
            maker_agent_id="developer",
            reviewer_agent_id="senior_dev",
        )

        # Final testing
        template.add_stage("testing", "tester", dependencies=["code_review"])

        errors = WorkflowValidationService.validate_workflow_template(template)

        assert errors == []

    def test_self_dependency_detected_as_circular(self):
        """Test that stage depending on itself is detected."""
        template = WorkflowTemplate.create(
            name="self_dep", display_name="Self Dependency"
        )
        template.add_stage("stage1", "agent_1", dependencies=["stage1"])  # Self-dependency

        errors = WorkflowValidationService.validate_workflow_template(template)

        # Should have both circular dependency and invalid dependency errors
        assert any("circular" in err.lower() or "invalid" in err.lower() for err in errors)

    def test_indirect_circular_dependency(self):
        """Test detection of indirect circular dependencies (A -> B -> C -> A)."""
        template = WorkflowTemplate.create(
            name="indirect_circular", display_name="Indirect Circular"
        )
        template.add_stage("stage_a", "agent_1", dependencies=["stage_c"])
        template.add_stage("stage_b", "agent_2", dependencies=["stage_a"])
        template.add_stage("stage_c", "agent_3", dependencies=["stage_b"])

        errors = WorkflowValidationService.validate_workflow_template(template)

        assert any("circular" in err.lower() for err in errors)


class TestHasCircularDependencies:
    """Tests for _has_circular_dependencies method."""

    def test_no_circular_dependencies(self, valid_template):
        """Test that linear workflow has no circular dependencies."""
        has_circular = WorkflowValidationService._has_circular_dependencies(
            valid_template
        )
        assert not has_circular

    def test_detects_simple_circular_dependency(self):
        """Test detection of simple circular dependency (A -> B -> A)."""
        template = WorkflowTemplate.create(
            name="circular", display_name="Circular"
        )
        template.add_stage("stage_a", "agent_1", dependencies=["stage_b"])
        template.add_stage("stage_b", "agent_2", dependencies=["stage_a"])

        has_circular = WorkflowValidationService._has_circular_dependencies(template)

        assert has_circular

    def test_detects_self_dependency(self):
        """Test detection of self-dependency."""
        template = WorkflowTemplate.create(
            name="self_dep", display_name="Self Dependency"
        )
        template.add_stage("stage_a", "agent_1", dependencies=["stage_a"])

        has_circular = WorkflowValidationService._has_circular_dependencies(template)

        assert has_circular

    def test_no_circular_with_parallel_stages(self):
        """Test that parallel stages don't create false positives."""
        template = WorkflowTemplate.create(
            name="parallel", display_name="Parallel Stages"
        )
        template.add_stage("initial", "agent_1")
        template.add_stage("parallel_1", "agent_2", dependencies=["initial"], is_parallel=True)
        template.add_stage("parallel_2", "agent_3", dependencies=["initial"], is_parallel=True)
        template.add_stage("merge", "agent_4", dependencies=["parallel_1", "parallel_2"])

        has_circular = WorkflowValidationService._has_circular_dependencies(template)

        assert not has_circular

    def test_complex_circular_dependency(self):
        """Test detection of complex circular dependency."""
        template = WorkflowTemplate.create(
            name="complex_circular", display_name="Complex Circular"
        )
        template.add_stage("a", "agent_1", dependencies=["b"])
        template.add_stage("b", "agent_2", dependencies=["c"])
        template.add_stage("c", "agent_3", dependencies=["d"])
        template.add_stage("d", "agent_4", dependencies=["a"])  # Closes the circle

        has_circular = WorkflowValidationService._has_circular_dependencies(template)

        assert has_circular
