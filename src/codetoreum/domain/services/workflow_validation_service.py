"""Workflow validation service for validating workflow configurations."""

from codetoreum.domain.workflow_template import WorkflowTemplate


class WorkflowValidationService:
    """
    Service for validating workflow configurations.

    Pure validation logic with no side effects.
    """

    @staticmethod
    def validate_workflow_template(template: WorkflowTemplate) -> list[str]:
        """
        Validate workflow template.

        Returns list of validation errors (empty if valid).

        Args:
            template: Workflow template to validate

        Returns:
            List of validation error messages (empty list if valid)
        """
        errors = []

        # Must have at least one stage
        if not template.stage_templates:
            errors.append("Workflow must have at least one stage")
            return errors

        stage_names = {st.name for st in template.stage_templates}

        # Check dependencies
        for stage in template.stage_templates:
            for dep in stage.dependencies:
                if dep not in stage_names:
                    errors.append(f"Stage '{stage.name}' has invalid dependency '{dep}'")

        # Check for cycles
        if WorkflowValidationService._has_circular_dependencies(template):
            errors.append("Workflow has circular dependencies")

        # Check review stages
        for stage in template.stage_templates:
            if stage.stage_type == "review":
                if not stage.maker_agent_id:
                    errors.append(f"Review stage '{stage.name}' missing maker agent")
                if not stage.reviewer_agent_id:
                    errors.append(f"Review stage '{stage.name}' missing reviewer agent")
                if stage.maker_agent_id == stage.reviewer_agent_id:
                    errors.append(f"Review stage '{stage.name}' has same maker and reviewer")

        # Check parallel stages limit
        parallel_count = sum(1 for st in template.stage_templates if st.is_parallel)
        if parallel_count > 10:
            errors.append(f"Too many parallel stages ({parallel_count}), max is 10")

        # Validate stage names (must be unique)
        if len(stage_names) != len(template.stage_templates):
            errors.append("Stage names must be unique")

        # Validate stage names are non-empty
        for stage in template.stage_templates:
            if not stage.name or not stage.name.strip():
                errors.append("Stage names cannot be empty")

        # Validate agent IDs are non-empty
        for stage in template.stage_templates:
            if not stage.agent_id or not stage.agent_id.strip():
                errors.append(f"Stage '{stage.name}' missing agent ID")

        return errors

    @staticmethod
    def _has_circular_dependencies(template: WorkflowTemplate) -> bool:
        """
        Check for circular dependencies using DFS.

        Args:
            template: Workflow template to check

        Returns:
            True if circular dependencies exist
        """
        visited = set()
        rec_stack = set()

        def visit(stage_name: str) -> bool:
            visited.add(stage_name)
            rec_stack.add(stage_name)

            stage = next(
                (s for s in template.stage_templates if s.name == stage_name),
                None,
            )

            if stage:
                for dep in stage.dependencies:
                    if dep not in visited:
                        if visit(dep):
                            return True
                    elif dep in rec_stack:
                        return True

            rec_stack.remove(stage_name)
            return False

        for stage in template.stage_templates:
            if stage.name not in visited:
                if visit(stage.name):
                    return True

        return False
